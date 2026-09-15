---
name: traceloom-setup
description: Explore a Python codebase and propose a plan to integrate TraceLoom — capture HTTP requests, logs, and exceptions in a local web dashboard. Use when the user wants to add TraceLoom to their project, set up request monitoring, debug logging, or capture outgoing API calls and crashes for debugging.
argument-hint: "[server_url]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, Bash(pip *), Bash(uv *), Bash(cat *), Bash(ls *), Bash(python *), Bash(docker *)
---

# Setup TraceLoom

You are helping the user integrate TraceLoom into their Python project. TraceLoom captures outgoing HTTP requests (via `requests`, `httpx`, `aiohttp`, and `botocore`), gRPC calls (via `grpc`), unhandled exceptions (via `sys.excepthook`), and Python log records (via `logging`). Everything is displayed in a unified timeline in a local web dashboard at http://localhost:5110. Google Cloud libraries (BigQuery, Firestore, Pub/Sub, Analytics Data API, Vertex AI, etc.) use gRPC under the hood and are captured automatically.

**Your job is to explore the codebase, then present a plan. Do NOT make any changes until the user approves.**

## Step 1: Explore the codebase

Investigate the project to understand:

1. **Package manager**: Is the project using `pip` + `requirements.txt`, `pip` + `pyproject.toml`, `uv`, `poetry`, `pipenv`, or something else?
2. **HTTP/gRPC libraries**: Does the project use `requests`, `httpx`, `aiohttp`, `grpc`, `botocore`, or Google Cloud client libraries? Search for `import requests`, `import httpx`, `from requests`, `from httpx`, `import grpc`, `from google.cloud`, `from google.analytics`, `import boto3`, `import botocore`.
3. **Logging usage**: Does the project use Python's `logging` module? Search for `import logging`, `logging.getLogger`, `logger.warning`, `logger.error`. This determines whether to suggest `capture_logs=True`.
4. **Application entrypoint**: Find where the app starts. Look for:
   - `if __name__ == "__main__":` blocks
   - Framework-specific entrypoints: Django (`manage.py`, `wsgi.py`, `asgi.py`), Flask (`app = Flask(...)`, `create_app()`), FastAPI (`app = FastAPI()`), etc.
   - CLI entrypoints in `pyproject.toml` (`[project.scripts]`)
   - For FastAPI or Django apps, note the app object / settings file location (needed for middleware setup)
5. **Docker setup**: Check for `docker-compose.yml`, `docker-compose.dev.yml`, `compose.yml`, `compose.dev.yml`, `Dockerfile`, or similar files. Identify development-specific compose files vs production ones.
6. **Environment-based config**: Check if the project uses environment variables, `.env` files, or settings modules to toggle dev-only features (this informs where to gate `traceloom.init()`).

## Step 2: Present the plan

After exploring, present a clear plan with these sections:

### A. Install the packages

The recommended approach is to install `traceloom` as a **regular (not dev) dependency**. It has zero dependencies itself, and `traceloom.init()` is a safe no-op when `TRACELOOM_URL` is not set — no patching, no threads, no side effects. This means users don't need conditional imports or `try/except ImportError` guards in production.

Based on the package manager detected:

- **pip + requirements.txt**: `pip install traceloom` (add `traceloom` to `requirements.txt`)
- **pip + pyproject.toml**: Add `traceloom` to `[project.dependencies]`
- **uv**: `uv add traceloom`
- **poetry**: `poetry add traceloom`
- **pipenv**: `pipenv install traceloom`

The server is covered separately in section D below.

### B. Pick an activation path

TraceLoom can be activated in two ways. Recommend **one** based on what fits the project; mention the other so the user knows it exists.

**Path 1 — code-level activation (`traceloom.init()`)**: explicit, lives next to other bootstrap code, easy to gate by environment. Best when the project owns its entrypoint and a couple of extra lines are welcome.

**Path 2 — wrapper (`traceloom run`)**: zero source changes. The user prepends `traceloom run` to whatever command they already use (`traceloom run uvicorn app:app`, `traceloom run pytest tests/`, `traceloom run my_app.py`). Best when:
- The entrypoint is owned by a framework or third-party tool that's awkward to edit (gunicorn/uvicorn workers, pytest, celery).
- The user just wants a one-off debugging session and doesn't want to touch source.
- Subprocess instrumentation needs to propagate to workers automatically (it does — PYTHONPATH is inherited).

`traceloom run` exposes the same `TRACELOOM_*` config as flags: `--server`, `--capture-host`, `--ignore-host`, `--capture-all`/`--no-capture-all`, `--redact-header`, `--redact-query-param`, `--capture-exceptions`/`--no-capture-exceptions`, `--capture-logs`/`--no-capture-logs`, `--log-level`, `--ignore-logger`. Flags win over env vars. Use `--` to disambiguate when the wrapped command's flags would collide (`traceloom run --server URL -- python -m mod --debug`).

#### B1. If using `traceloom.init()`

Propose the exact file and location. The two lines must go **before** any HTTP library imports or usage so HTTP patching catches the first request:

```python
import traceloom
traceloom.init()
```

Ordering nuance for the other capture types:

- **Exceptions** (on by default — `capture_exceptions=True`): `init()` installs `sys.excepthook` / `threading.excepthook` immediately. Position doesn't matter beyond running before the exception happens — for unhandled exceptions in the bootstrap path itself, place `init()` as early as possible. Pass `capture_exceptions=False` (or `TRACELOOM_CAPTURE_EXCEPTIONS=false`) to opt out.
- **Logs** (off by default — opt in with `capture_logs=True`): logging capture works regardless of when handlers and loggers are created — TraceLoom hooks `Logger.callHandlers`, which all log calls funnel through. So even loggers configured later (Django settings, `logging.config.dictConfig`, etc.) are captured.

Common placement patterns:

- **Django**: In `manage.py` (for `runserver`) or a custom `AppConfig.ready()` method
- **Flask**: At the top of `create_app()` or the app factory
- **FastAPI**: At module level in the main app file, or in a `lifespan` handler
- **CLI / script**: Near the top of `if __name__ == "__main__":`
- **General**: Wherever the application bootstraps, before HTTP calls are made

Since TraceLoom uses the server URL as its activation signal, the recommended pattern is to always call `traceloom.init()` and control activation via the `TRACELOOM_URL` environment variable:

```python
import traceloom
traceloom.init()  # only activates when TRACELOOM_URL is set
```

Then in `.env` or the shell:

```bash
TRACELOOM_URL=http://localhost:5110
```

This way the code has zero conditional logic — without `TRACELOOM_URL`, `init()` is a safe no-op (no patching, no threads, no side effects).

If the project uses logging extensively, suggest enabling log capture:

```python
import traceloom
traceloom.init(capture_logs=True, log_level=20)  # capture INFO and above
```

If the project uses noisy framework loggers (e.g., `uvicorn.access`, `django.request`), suggest suppressing them:

```python
traceloom.init(capture_logs=True, log_level=20, ignore_loggers=["uvicorn.access"])
```

Or via environment variables:

```bash
TRACELOOM_CAPTURE_LOGS=true
TRACELOOM_LOG_LEVEL=20
TRACELOOM_IGNORE_LOGGERS=uvicorn.access
```

Exception capture is enabled by default — no configuration needed.

#### B2. If using `traceloom run`

No source edits. The user runs their existing command through the wrapper:

```bash
# .py scripts run with the current Python interpreter
traceloom run my_app.py

# Console scripts work directly; subprocess workers are instrumented automatically
traceloom run uvicorn app:app
traceloom run gunicorn app:app
traceloom run pytest tests/

# `--` disambiguates when the wrapped command and traceloom share flag names
traceloom run --server http://localhost:5110 -- python -m my_module --debug

# Enable log + exception capture without code changes
traceloom run --capture-logs --log-level 20 uvicorn app:app
```

If the project ships its own `traceloom.init()` call already, the wrapper is still safe to use: bootstrap initialization runs first, then the program's `init()` updates the live config in place (no double-patching, no double-capture).

For long-running commands defined in `Procfile`, `Makefile`, `justfile`, `package.json` scripts, or compose files, suggest prefixing the command with `traceloom run` in dev variants only.

### C. Configure via environment variables

TraceLoom supports full configuration via `TRACELOOM_*` environment variables. Suggest adding these to the project's `.env`, `.env.development`, or equivalent:

```bash
TRACELOOM_URL=http://localhost:5110                  # server URL (activates TraceLoom)
# TRACELOOM_CAPTURE_HOSTS=api.stripe.com,api.openai.com  # only capture these hosts
# TRACELOOM_IGNORE_HOSTS=localhost,internal.svc      # skip these hosts
# TRACELOOM_REDACT_HEADERS=Authorization,X-Api-Key   # headers to redact
# TRACELOOM_CAPTURE_LOGS=true                         # capture Python log records
# TRACELOOM_LOG_LEVEL=20                              # minimum log level (INFO=20, WARNING=30)
# TRACELOOM_IGNORE_LOGGERS=uvicorn.access             # suppress noisy loggers
```

All parameters can also be passed explicitly to `traceloom.init()`, which takes precedence over env vars:

- If the app talks to specific APIs, suggest `TRACELOOM_CAPTURE_HOSTS=api.example.com` or `capture_hosts=["api.example.com"]`
- If there are internal services to skip, suggest `TRACELOOM_IGNORE_HOSTS=...` or `ignore_hosts=[...]`
- If a non-default server URL is needed (e.g., Docker networking), suggest `TRACELOOM_URL=http://traceloom:5110` or `server_url="http://traceloom:5110"`
- If the project uses logging heavily, suggest `TRACELOOM_CAPTURE_LOGS=true` with an appropriate `TRACELOOM_LOG_LEVEL`
- If framework loggers are noisy, suggest `TRACELOOM_IGNORE_LOGGERS=uvicorn.access` or `ignore_loggers=["uvicorn.access"]`
- Always mention that `Authorization` and `X-Api-Key` headers are redacted by default
- Mention that unhandled exception capture is on by default

Boolean env vars accept `true`/`1`/`yes` and `false`/`0`/`no` (case-insensitive). List env vars are comma-separated.

### D. Add incoming request middleware (if applicable)

If the project is a **FastAPI** or **Django** web application, suggest adding the TraceLoom middleware to capture incoming HTTP requests. This is the one integration that always requires a code change (it cannot be done via `traceloom run` alone).

#### FastAPI

```python
from traceloom.integrations.fastapi import TraceLoomMiddleware
from fastapi import FastAPI

app = FastAPI()
app.add_middleware(TraceLoomMiddleware, ignore_paths=["/health"])
```

#### Django

```python
# settings.py
MIDDLEWARE = [
    "traceloom.integrations.django.TraceLoomMiddleware",
    ...
]
TRACELOOM_IGNORE_PATHS = ["/health/", "/admin/"]
```

The middleware captures every request your server handles: method, path, status code, duration, route pattern, and client IP. Unhandled exceptions are captured with full tracebacks.

Only suggest this if the project is a web application. For CLI tools, scripts, or background workers, skip this section.

### E. Set up the server

**Ask the user** which server setup they prefer:

1. **No server setup** — they'll install and run `traceloom-server` separately (skip this section)
2. **Docker Compose** — add a TraceLoom service to their compose file
3. **Development dependency** — add `traceloom-server` to their project's dev dependencies

`pip install traceloom-server` includes the full web dashboard — Docker is not required for the UI.

#### Option: Docker Compose

If the user chooses Docker Compose, propose adding a TraceLoom service:

```yaml
traceloom:
  build: .
  ports:
    - "5110:5110"
  volumes:
    - traceloom-data:/data
```

And add `traceloom-data` to the `volumes:` section. The app container should set `TRACELOOM_URL=http://traceloom:5110` (or pass `server_url="http://traceloom:5110"` to `init()`) to reach the TraceLoom server over the Docker network.

Prefer adding this to a dev-specific compose file (`docker-compose.dev.yml`, `compose.dev.yml`, `compose.override.yml`) if one exists. If only a single compose file exists, note that the user may want to create a dev overlay.

#### Option: Development dependency

If the user chooses to add the server as a dev dependency, use the same package manager pattern from section A:

- **pip + requirements.txt**: Add `traceloom-server` to `requirements-dev.txt`
- **pip + pyproject.toml**: Add `traceloom-server` to the dev dependency group
- **uv**: `uv add --dev traceloom-server`
- **poetry**: `poetry add --group dev traceloom-server`
- **pipenv**: `pipenv install --dev traceloom-server`

Then run with `traceloom-server`, or as a standalone tool:

```bash
# With uv
uv tool install traceloom-server

# With pipx
pipx install traceloom-server
```

## Step 3: Wait for approval

After presenting the plan, ask the user which parts they want to proceed with. Do NOT edit any files until explicitly told to do so.

## Reference

- TraceLoom client SDK: `pip install traceloom` (Python >= 3.10, zero dependencies)
- TraceLoom server: `pip install traceloom-server` (Python >= 3.14, includes web dashboard)
- Dashboard: http://localhost:5110 (served by both pip install and Docker)
- Captures: outgoing HTTP requests (`requests`, `httpx`, `aiohttp`, `grpc`, `botocore`), incoming HTTP requests (FastAPI/Django middleware), unhandled exceptions (`sys.excepthook`), and Python log records (`logging`)
- Default redacted headers: `Authorization`, `X-Api-Key`
- Default server URL: `http://localhost:5110`
- `traceloom run` wrapper: zero-code activation via `PYTHONPATH` bootstrap; subprocess-instrumentation safe; flags mirror `TRACELOOM_*` env vars 1:1.

### Environment variables

| Variable | Type | Default |
|----------|------|---------|
| `TRACELOOM_URL` | string | `None` (inactive) |
| `TRACELOOM_CAPTURE_ALL` | bool | `true` |
| `TRACELOOM_CAPTURE_HOSTS` | comma-separated list | `[]` |
| `TRACELOOM_IGNORE_HOSTS` | comma-separated list | `[]` |
| `TRACELOOM_REDACT_HEADERS` | comma-separated list | `Authorization,X-Api-Key` |
| `TRACELOOM_REDACT_QUERY_PARAMS` | comma-separated list | `[]` |
| `TRACELOOM_CAPTURE_EXCEPTIONS` | bool | `true` |
| `TRACELOOM_CAPTURE_LOGS` | bool | `false` |
| `TRACELOOM_LOG_LEVEL` | int | `30` (WARNING) |
| `TRACELOOM_IGNORE_LOGGERS` | comma-separated list | `[]` |

Precedence: explicit `init()` parameter > env var > hardcoded default.
