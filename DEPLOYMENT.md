# Deployment

ckl-bench is a single-process, zero-dependency (stdlib-only core) evaluation
server. It runs on a single node and has no external services — no Redis, no
database server, no message queue. All state is local files.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  ckl-bench server (one Python process)                       │
│                                                              │
│  HTTP API   :8765   ── ThreadingHTTPServer (stdlib)          │
│  WebSocket  :8766   ── websockets library (optional)         │
│                                                              │
│  RunManager ── background-thread run workers                  │
│      │                                                       │
│      ├── RunDB (SQLite, runs/ckl-bench.db)                   │
│      ├── ResponseCache (content-addressed, .ckl_bench_cache) │
│      └── runs/<run-id>/  results.jsonl, summary.json, etc.   │
│                                                              │
│  Logging subsystem (core/logging_config.py):                 │
│      QueueHandler → QueueListener → AggregatingHandler       │
│                         ├── RotatingFileHandler (async file)  │
│                         └── StreamHandler (aggregated console)│
└─────────────────────────────────────────────────────────────┘
```

### Logging: async + aggregated

The logging subsystem (`ckl_bench/core/logging_config.py`) keeps the server
responsive during long runs:

- **Async file writing** — all log records are handed off to a background
  thread via `QueueHandler` / `QueueListener`. File I/O never blocks the run
  workers or the HTTP/WebSocket event loop.
- **Aggregated console** — a custom `AggregatingHandler` collapses consecutive
  identical log lines into one annotated line, e.g. 100 identical
  "case started" messages become one `... (repeated 100x)` line. This keeps
  the console readable during long runs.
- **Bounded growth** — the file handler rotates at 5 MB × 3 backups.

## Quick start

```bash
# Foreground (Ctrl+C to stop)
ckl serve --host 127.0.0.1 --port 8765

# Background daemon
ckl serve --daemon --port 8765
ckl serve status
ckl serve stop
```

The dashboard is at `http://<host>:<port>`.

## Configuration

### Command-line flags

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind host. Use `0.0.0.0` for LAN access. |
| `--port` | `8765` | HTTP port. WebSocket runs on `port + 1`. |
| `--runs` | `runs` | Directory for run data and SQLite DB. |
| `--cases` | `cases` | Directory for case files. |
| `--log-file` | unset | Path to rotating log file. If unset, logs go to console only. |
| `--log-level` | `INFO` | Minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `--daemon` | off | Run in the background. |
| `--open` | off | Open the dashboard in a browser after start. |

### Environment variables

| Variable | Description |
|----------|-------------|
| `CKL_LOG_FILE` | Default log file path. Overridden by `--log-file`. |
| `CKL_CACHE_DIR` | Response cache directory. |
| `CKL_JUDGE` | Judge target (e.g. `deepseekv4`). Defaults to `dsx` when unset. |
| `CKL_REVIEWER` | Default reviewer target. |
| `CKL_VERIFIER` | Default verifier target. |
| `CKL_LOCAL_BASE_URL` | Local OpenAI-compatible endpoint URL. |
| `CKL_AGENT_COMMAND` | Command for the generic agent wrapper. |
| `CKL_CODEX_COMMAND` | Command for the Codex wrapper. |
| `CKL_DSX_COMMAND` | Command for the DSX wrapper. |
| `CKL_CLAUDE_COMMAND` | Command for the Claude Code wrapper. |
| `CKL_GEMINI_COMMAND` | Command for the Gemini wrapper. |
| `OPENAI_API_KEY` | OpenAI API key. |
| `ANTHROPIC_API_KEY` | Anthropic API key. |
| `GEMINI_API_KEY` | Google AI API key. |
| `OPENROUTER_API_KEY` | OpenRouter API key. |

API keys can also be placed in a `.env` file in the working directory.

### Daemon mode

In daemon mode, the server forks into the background:

- PID is written to `~/.ckl_bench/server.pid`.
- If `--log-file` is not set, logs default to `~/.ckl_bench/server.log`.
- `ckl serve stop` sends `SIGTERM` to the recorded PID.
- `ckl serve status` checks if the PID is alive.

## tmux deployment used by this checkout

The local deployment runs in tmux session `ckl`, pane `ckl:1.1`, from the
repository root:

```bash
tmux new-session -d -s ckl -c /path/to/ckl-bench \
  'python -m ckl_bench serve --host 127.0.0.1 --port 8765'
```

Safe redeploy after verification:

```bash
tmux send-keys -t ckl:1.1 C-c
# wait until ports 8765/8766 are free
tmux send-keys -t ckl:1.1 \
  'python -m ckl_bench serve --host 127.0.0.1 --port 8765' Enter
curl --fail http://127.0.0.1:8765/api/config
```
## Production notes

- **Single node only.** All state is local; there is no cross-node
  coordination. Run multiple instances only if they use separate `--runs`
  directories.
- **No auth built in.** Bind to `127.0.0.1` (the default) and put the server
  behind a reverse proxy (nginx, Caddy) for TLS and authentication if exposed
  beyond localhost.
- **WebSocket port.** The WebSocket server runs on `port + 1` (8766 by
  default). Ensure both ports are reachable by clients.
- **Disk usage.** Each run writes `results.jsonl`, `summary.json`, and
  `report.html` under `runs/<run-id>/`. The SQLite DB grows with run count;
  prune old run directories as needed.
- **Log rotation.** The log file rotates at 5 MB × 3 backups, so disk usage
  is bounded to ~20 MB.
