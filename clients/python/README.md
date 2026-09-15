<p align="center">
  <img src="../../docs/assets/logo.png" alt="TraceLoom logo" width="160">
</p>

# TraceLoom

Capture outgoing and incoming HTTP requests, pytest results, Python logs, and unhandled exceptions in a local web dashboard.

Like [Mailpit](https://mailpit.axllent.org/), but for your entire debug output.

## Setup

From the repository root, install the workspace dependencies:

```bash
uv sync --frozen
```

Start the server:

```bash
traceloom-server
```

Run your code with TraceLoom:

```bash
traceloom run my_app.py
traceloom run pytest tests/
traceloom run uvicorn app:app
```

That's it. TraceLoom activates before your code runs and captures outgoing traffic, pytest results, unhandled exceptions, and optional Python log records. No code changes needed.

Subprocess instrumentation propagates automatically through `PYTHONPATH`, so `traceloom run gunicorn app:app` also captures traffic from worker processes.

CLI flags map 1:1 to the `TRACELOOM_*` env vars: `--server`, `--capture-host`, `--ignore-host`, `--capture-all` / `--no-capture-all`, `--redact-header`, `--redact-query-param`, `--capture-tests` / `--no-capture-tests`, `--capture-logs`, `--log-level`, `--app`, `--session`. The action-only `--clear` flag does not set an environment variable.

Clear all events with `traceloom clear`, or begin a command with an empty timeline:

```bash
traceloom run --clear my_app.py
```

Query captured events without opening the dashboard:

```bash
traceloom query
traceloom query --session debug-payment --type http --status 500 --ancestors
traceloom query --session debug-payment --after-seq 1642
traceloom query --session debug-payment --stats
traceloom query 5ae54ca2
traceloom query 'http://localhost:5110/#5ae54ca2-45a7-45a6-a6cd-533569fc8db7'
traceloom meta
```

List queries use compact text by default and indent events by their runtime hierarchy,
adding an `app/session` column when the results span more than one run. Pass
`--format json` or `--format jsonl` for shell pipelines. Pass a displayed
eight-character ID, full UUID, or dashboard URL to print the complete event as
formatted JSON. `traceloom meta` lists every app, session, host, event type, and method
the server has captured.

Tag events with `--app` and `--session` to isolate a debugging run:

```bash
traceloom run --app myapp --session debug-payment python scripts/checkout.py
```

### Using `traceloom.init()` instead

If you prefer to activate TraceLoom from within your code (e.g., for programmatic configuration or projects with a custom `sitecustomize.py`):

```python
import traceloom
traceloom.init()  # activates only when TRACELOOM_URL is set
```

### Framework middleware

To capture incoming requests, add the TraceLoom middleware to your web framework:

**FastAPI:**

```python
from traceloom.integrations.fastapi import TraceLoomMiddleware
from fastapi import FastAPI

app = FastAPI()
app.add_middleware(TraceLoomMiddleware, ignore_paths=["/health"])
```

**Django:**

```python
# settings.py
MIDDLEWARE = [
    "traceloom.integrations.django.TraceLoomMiddleware",
    ...
]
TRACELOOM_IGNORE_PATHS = ["/health/", "/admin/"]
```

Then run with `traceloom run`:

```bash
traceloom run uvicorn app:app        # FastAPI
traceloom run manage.py runserver    # Django
```

The middleware captures method, path, status code, duration, route pattern, client IP, and request/response bodies. Unhandled exceptions are captured with full tracebacks. When TraceLoom is inactive (no server URL configured), the middleware passes requests through without capturing anything.

### Google Cloud libraries

Many Google Cloud Python libraries — BigQuery, Firestore, Pub/Sub, Analytics Data API (GA4), Vertex AI, Speech-to-Text, Vision, Translation, and others — use gRPC under the hood. TraceLoom captures these calls automatically:

```bash
traceloom run my_bigquery_script.py
```

Any library that calls `grpc.secure_channel()` or `grpc.insecure_channel()` is automatically captured.

## What TraceLoom captures

**Outgoing HTTP requests** — method, URL, headers, body, response status/headers/body, duration, and library used (requests, httpx, aiohttp, grpc, or botocore).

Failed outgoing calls retain exception details. If a library raises after receiving a
response, TraceLoom stores both the response status and headers and the exception.

**Incoming HTTP requests** (via FastAPI or Django middleware) — method, path, route pattern, status code, duration, client IP, request/response headers and bodies, plus exception tracebacks if a handler raises.

**Pytest executions** (enabled by default): TraceLoom supports pytest 7 and later and records one event per test function or method invocation. Parametrized cases remain separate. The repository's frozen workspace includes the pytest integration.

Each event includes the outcome, fixture names, source location, total and per-phase timings, and failure details. It also carries runtime trace and span IDs plus stable directory, file, class, and unparameterized case memberships. Outgoing Requests, HTTPX, aiohttp, botocore, and gRPC calls inherit those memberships and appear as child operations. The dashboard always shows runtime parenthood and can add one virtual grouping by an available pytest level or remote host without changing event deep links. Virtual groups merge only across adjacent siblings, which preserves record order. Timeline filters retain matching records' runtime ancestors, so filtered children remain connected to their runtime context. The traceback generated by pytest may include `repr()` output for parameter, fixture, or local variable values.

See the local `docs/guides/debug-pytest.md` for a runnable example and dashboard walkthrough.

**Unhandled exceptions** (enabled by default) — exception type, message, full traceback, and stack frames with source context.

**Log records** (opt-in via `capture_logs=True`) — level, logger name, message, source location, and extra attributes.

TraceLoom redacts sensitive headers (`Authorization`, `X-Api-Key`) by default and optionally redacts query string parameters.

## Configuration

```python
traceloom.init(
    server_url="http://localhost:5110",       # where to send captured data

    # HTTP capture
    capture_hosts=["api.stripe.com"],         # only capture these hosts
    capture_all=True,                          # capture everything (default)
    ignore_hosts=["localhost"],               # skip these hosts
    redact_headers=["Authorization"],         # replace header values with [REDACTED]
    redact_query_params=["api_key", "token"], # replace query param values with [REDACTED]

    # Tests, logs, and exceptions
    capture_tests=True,                        # capture pytest executions (default)
    capture_exceptions=True,                   # capture unhandled exceptions (default)
    capture_logs=False,                        # capture log records (opt-in)
    log_level=30,                              # minimum log level to capture (WARNING)
    ignore_loggers=["uvicorn.access"],         # suppress noisy framework loggers

    # Tagging
    app="myapp",                               # tag events with an application name
    session="debug-payment",                   # tag events with a session ID
)
```

All parameters fall back to `TRACELOOM_*` environment variables when not passed explicitly:

| Parameter | Env variable | Default |
|-----------|-------------|---------|
| `server_url` | `TRACELOOM_URL` | `None` (inactive) |
| `capture_all` | `TRACELOOM_CAPTURE_ALL` | `True` |
| `capture_hosts` | `TRACELOOM_CAPTURE_HOSTS` | `[]` |
| `ignore_hosts` | `TRACELOOM_IGNORE_HOSTS` | `[]` |
| `redact_headers` | `TRACELOOM_REDACT_HEADERS` | `["Authorization", "X-Api-Key"]` |
| `redact_query_params` | `TRACELOOM_REDACT_QUERY_PARAMS` | `[]` |
| `capture_tests` | `TRACELOOM_CAPTURE_TESTS` | `True` |
| `capture_exceptions` | `TRACELOOM_CAPTURE_EXCEPTIONS` | `True` |
| `capture_logs` | `TRACELOOM_CAPTURE_LOGS` | `False` |
| `log_level` | `TRACELOOM_LOG_LEVEL` | `30` (WARNING) |
| `ignore_loggers` | `TRACELOOM_IGNORE_LOGGERS` | `[]` |
| `app` | `TRACELOOM_APP` | `""` |
| `session` | `TRACELOOM_SESSION` | `""` |

The server URL is the activation signal — `init()` does nothing unless `server_url` is passed or `TRACELOOM_URL` is set. Boolean env vars accept `true`/`1`/`yes` and `false`/`0`/`no` (case-insensitive). List env vars are comma-separated.

TraceLoom Server deletes events older than seven days when it starts and every hour after that. Set `TRACELOOM_RETENTION_DAYS` on the server process to change the retention period, or set it to `0` to keep events indefinitely. The server rejects negative or malformed values at startup.

Calls to the OpenAI, Anthropic, and Gemini APIs render as a readable conversation in the dashboard, with the system prompt, tool calls, and token usage broken out. The raw JSON stays one tab away.

## Supported libraries

- **requests** — patches `Session.send()`
- **httpx** — patches `Client.send()` and `AsyncClient.send()`
- **aiohttp** — injects `TraceConfig` lifecycle hooks to capture async HTTP traffic
- **grpc** — patches `insecure_channel()` and `secure_channel()` to intercept unary-unary calls
- **botocore** — patches `URLLib3Session.send()` to capture boto3 / AWS SDK traffic
- **pytest**: loads a plugin that captures each test function or method invocation

## Requires

- Python >= 3.10
- [traceloom-server](https://pypi.org/project/traceloom-server/) running locally

## Links

- [traceloom-server on PyPI](https://pypi.org/project/traceloom-server/)
