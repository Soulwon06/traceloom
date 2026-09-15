# Getting Started

## Install

Install the client SDK and the server:

```bash
uv sync --frozen
```

Start the server:

```bash
traceloom-server
```

The server listens at [http://localhost:5110](http://localhost:5110). The `127.0.0.1:` prefix keeps it accessible only from your machine. Omit it if you need LAN access.

!!! tip "Why port 5110?"
    Read it as **5-1-1-0** → **S-L-L-O** → **traceloom**.

## Run your code with TraceLoom

Prefix any Python command with `traceloom run`:

```bash
traceloom run my_app.py
traceloom run pytest tests/
traceloom run uvicorn app:app
```

That's it. TraceLoom activates before your code runs and captures outgoing traffic, pytest results, and unhandled exceptions. No code changes needed.

Subprocess instrumentation propagates automatically, so `traceloom run gunicorn app:app` also captures traffic from worker processes.

Use `--` to disambiguate when traceloom flags conflict with the wrapped command's flags:

```bash
traceloom run --capture-logs --log-level INFO -- python -m my_module --debug
```

CLI flags map 1:1 to the [environment variables](configuration.md):

| Flag                    | Env var                       |
| ----------------------- | ----------------------------- |
| `--server`              | `TRACELOOM_URL`                  |
| `--debug` / `--no-debug` | `TRACELOOM_DEBUG`               |
| `--capture-host`        | `TRACELOOM_CAPTURE_HOSTS`        |
| `--ignore-host`         | `TRACELOOM_IGNORE_HOSTS`         |
| `--capture-all` / `--no-capture-all` | `TRACELOOM_CAPTURE_ALL` |
| `--redact-header`       | `TRACELOOM_REDACT_HEADERS`       |
| `--redact-query-param`  | `TRACELOOM_REDACT_QUERY_PARAMS`  |
| `--capture-tests` / `--no-capture-tests` | `TRACELOOM_CAPTURE_TESTS` |
| `--capture-logs` / `--no-capture-logs` | `TRACELOOM_CAPTURE_LOGS` |
| `--log-level`           | `TRACELOOM_LOG_LEVEL`            |
| `--ignore-logger`       | `TRACELOOM_IGNORE_LOGGERS`       |
| `--app`                 | `TRACELOOM_APP`                  |
| `--session`             | `TRACELOOM_SESSION`              |

## Query captured events

Use `traceloom query` to inspect the same events as the dashboard from a terminal. Lists
default to hierarchy-aware text, and a displayed event ID opens its complete JSON data:

```bash
traceloom query
traceloom query --session debug-payment --type http --status 500 --ancestors
traceloom query 5ae54ca2
traceloom meta
```

`traceloom meta` lists every app, session, host, event type, and method on the server,
which is the quickest way to find out what you can filter for.

See [Query captured events](query.md) for filters, output formats, event and dashboard
URL lookups, hierarchy behavior, and server selection.

### Using `traceloom.init()` instead

If you prefer to activate TraceLoom from within your code, call `traceloom.init()`:

```python
import traceloom
traceloom.init()
```

TraceLoom only activates when a server URL is provided, either via the `server_url` parameter or the `TRACELOOM_URL` environment variable. Without a URL, `init()` is a safe no-op: no monkey-patching, no background threads, no side effects.

```bash
# Activate in development
export TRACELOOM_URL=http://localhost:5110
```

Like Sentry's `SENTRY_DSN`, this keeps instrumentation in place with zero production overhead. `traceloom.init()` is also the right choice for projects with a custom `sitecustomize.py`, where `traceloom run` can't be used.

### FastAPI middleware

To capture incoming HTTP requests in a FastAPI app, add the TraceLoom middleware:

```python
from traceloom.integrations.fastapi import TraceLoomMiddleware
from fastapi import FastAPI

app = FastAPI()
app.add_middleware(TraceLoomMiddleware)
```

Then run your server with `traceloom run`:

```bash
traceloom run uvicorn app:app
```

Every request your server handles appears in the dashboard with method, path, status code, duration, route pattern, and client IP. If a route handler raises an unhandled exception, the middleware captures the traceback before re-raising.

By default, all paths are captured. Use `ignore_paths` to skip noisy endpoints like health checks and OpenAPI schema routes. Matching is prefix-based:

```python
app.add_middleware(TraceLoomMiddleware, ignore_paths=["/health", "/openapi.json", "/docs"])
```

The middleware is a raw ASGI middleware (not Starlette's `BaseHTTPMiddleware`), so it works with streaming responses and background tasks. When TraceLoom is inactive (no server URL configured), the middleware passes requests through without capturing anything.

### Django middleware

To capture incoming HTTP requests in a Django app, add the TraceLoom middleware at the top of your `MIDDLEWARE` list:

```python
# settings.py
MIDDLEWARE = [
    "traceloom.integrations.django.TraceLoomMiddleware",  # first — sees the raw request
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    # ...
]
```

Then run your server with `traceloom run`:

```bash
traceloom run manage.py runserver
```

Every request your server handles appears in the dashboard with method, path, status code, duration, route pattern, and client IP. If a view raises an unhandled exception, the middleware captures the traceback via Django's `process_exception` hook.

By default, all paths are captured. Use the `TRACELOOM_IGNORE_PATHS` setting to skip noisy endpoints. Matching is prefix-based:

```python
TRACELOOM_IGNORE_PATHS = ["/health/", "/admin/", "/static/"]
```

When TraceLoom is inactive (no server URL configured), the middleware passes requests through without capturing anything.

### Exploring hierarchy views

The local hierarchy demo creates an incoming FastAPI request, logs inside its handler,
and successful or failed outgoing HTTP child operations. Start it with log capture:

```bash
traceloom run --capture-logs --log-level INFO -- \
  uvicorn examples.python.hierarchy_demo:app --port 8001
```

Open `http://localhost:8001/docs` and call `POST /checkout` and
`POST /checkout/provider-down`. TraceLoom always places child operations beneath their
runtime parents. Choose **Remote host** to insert destination groups where outgoing calls
begin. Virtual groups preserve runtime parenthood, keep chronological sibling order, and
count only loaded records.
Filtering the timeline keeps the runtime ancestors of matching records visible, so child
operations and annotations remain connected to their runtime context.

See [`hierarchy_demo.py`](../examples/python/hierarchy_demo.py)
and [Hierarchy and data model](data-model.md) for the full projection and filtering
behavior.

### Capturing pytest tests

The bundled plugin supports pytest 7 and later. Install the pytest extra if your project doesn't already include pytest:

```bash
uv sync --frozen
```

Pytest capture is enabled by default. Run pytest through TraceLoom:

```bash
traceloom run pytest tests/
```

The plugin creates one event for every test function or method invocation. Parametrized cases appear separately under their full node IDs. Each event includes its outcome, fixture names, source location, timings, and failure details.

The traceback generated by pytest may include `repr()` output for parameter, fixture, or local variable values. With pytest-xdist, events also include the shared run ID and worker ID.

TraceLoom keeps one runtime operation active across each test's setup, call, and teardown.
The event also identifies its directory, file, class, and unparameterized case so API
clients can build navigation groups without treating those virtual groups as executed
spans. Outgoing Requests, HTTPX, aiohttp, botocore, and gRPC calls made during the test
inherit that collection path and record the test operation as their runtime parent.
Use the dashboard's **Group** selector to add one available pytest level or remote-host
grouping to the runtime tree. See [Hierarchy and data model](data-model.md) for the wire
format and projection behavior.

See [Debug pytest tests with TraceLoom](guides/debug-pytest.md) for a runnable parametrized failure example and dashboard walkthrough.

Disable this capture without affecting HTTP, logs, or exceptions:

```bash
traceloom run --no-capture-tests pytest tests/
```

### Capturing logs

Log capture is opt-in. Enable it to see Python log records alongside your HTTP traffic and exceptions in the same timeline:

```bash
traceloom run --capture-logs --log-level INFO my_app.py
```

Or with `traceloom.init()`:

```python
import traceloom
traceloom.init(capture_logs=True, log_level=20)
```

TraceLoom's own loggers (`traceloom.*`) and `urllib3` loggers are always excluded to prevent recursion. You can suppress other noisy loggers with `ignore_loggers`:

```bash
traceloom run --capture-logs --ignore-logger uvicorn.access --ignore-logger uvicorn.error my_app.py
```

Matching is hierarchical: `"uvicorn"` suppresses `uvicorn`, `uvicorn.access`, `uvicorn.error`, etc. See [ignore_loggers](configuration.md#ignore_loggers) for details.

### Capturing exceptions

Unhandled exceptions are captured by default. No configuration needed. When your program crashes, TraceLoom captures the full traceback with stack frames and source context, then flushes the event before the process exits.

To disable exception capture: `traceloom run --no-capture-exceptions my_app.py` or `traceloom.init(capture_exceptions=False)`.

### Debugging sessions

Tag events with `--app` and `--session` to isolate a debugging run without clearing existing data:

```bash
traceloom run --app myapp --session debug-payment python scripts/checkout.py
```

Then filter the dashboard or API to see only events from that session:

```bash
curl -s 'http://localhost:5110/api/events?app=myapp&session=debug-payment'
```

This is useful when you have multiple services or scripts running at the same time — give each its own `--app` name and a shared `--session` to see the full picture. See [configuration](configuration.md#app) for more.

### Google Cloud libraries

Many Google Cloud Python libraries use gRPC under the hood. TraceLoom captures these calls automatically. No extra setup needed:

```bash
traceloom run my_bigquery_script.py
```

BigQuery, Firestore, Pub/Sub, Analytics (GA4), Vertex AI, Speech-to-Text, Vision, Translation: anything that calls `grpc.secure_channel()` or `grpc.insecure_channel()` is captured.

### AWS libraries (boto3)

boto3 uses `botocore`, which calls `urllib3` directly, bypassing `requests` and `httpx`. TraceLoom patches botocore's HTTP session to capture all AWS API calls:

```bash
traceloom run my_aws_script.py
```

AWS calls appear at `http://localhost:5110`. XML responses show as a collapsible tree, just like JSON.

## Troubleshooting

If TraceLoom appears to be running but you don't see events in the dashboard, enable debug mode:

```bash
# Via CLI flag
traceloom run --debug my_app.py

# Via environment variable
TRACELOOM_DEBUG=1 traceloom run my_app.py

# In code
traceloom.init(server_url="http://localhost:5110", debug=True)
```

Debug mode logs to stderr: the resolved configuration and where each value came from, which libraries were patched, every capture/skip decision, and whether the server is reachable. See [configuration](configuration.md#debug) for details.

## What TraceLoom captures

### Outgoing HTTP requests

For every outgoing HTTP and gRPC call:

- Method, URL, headers, and body
- Response status code, headers, and body
- Duration in milliseconds
- Library used (requests, httpx, aiohttp, grpc, or botocore)

The dashboard recognizes Unix timestamps in JSON bodies and shows the human-readable date in a tooltip. XML responses (common in AWS S3, STS, EC2) appear as a collapsible tree, just like JSON. Both formats offer Tree and Raw tabs. Tree shows an expandable tree; Raw shows syntax-highlighted source.

gRPC calls are displayed with a `grpc://` URL scheme. Protobuf request and response bodies are automatically serialized to JSON.

### Incoming HTTP requests

When you add the [FastAPI](#fastapi-middleware) or [Django](#django-middleware) middleware, TraceLoom captures every request your server handles:

- Method, path, full URL, and route pattern (e.g., `/api/users/{id}`)
- Request and response headers and bodies
- Response status code and duration
- Client IP address
- Exception type and traceback (if the handler raises)

Request and response bodies are capped at 1 MB, matching the outgoing capture limit.

### Pytest tests

For each pytest test function or method invocation, TraceLoom captures:

- Status: passed, failed, error, skipped, xfailed, or xpassed
- Total duration and setup, call, and teardown timings
- Fixture names
- Test node ID, source file, line number, and function or method name
- Assertion, setup, and teardown failure details, including pytest's formatted traceback
- Test run and xdist worker identifiers

Parametrized tests produce one event per parameter set.

### Logs

When `capture_logs=True`, TraceLoom captures Python log records at or above the configured `log_level`:

- Level (DEBUG, INFO, WARNING, ERROR, CRITICAL), logger name, and formatted message
- Source file path, line number, and function name
- Extra attributes attached to the record via `extra={...}`

TraceLoom's own loggers (`traceloom.*`) and `urllib3` loggers are automatically excluded to prevent recursion.

### Exceptions

Unhandled exceptions are captured with:

- Exception type, message, and module
- Full formatted traceback text
- Individual stack frames with filename, line number, function name, and source context line

Both `sys.excepthook` (main thread) and `threading.excepthook` (worker threads) are hooked.

TraceLoom redacts sensitive headers (`Authorization`, `X-Api-Key`) by default and optionally redacts query string parameters ([details](configuration.md#redact_query_params)).

## Supported libraries

| Library      | What TraceLoom patches                                    |
| ------------ | ------------------------------------------------------ |
| **requests** | `Session.send()`                                       |
| **httpx**    | `Client.send()` and `AsyncClient.send()`               |
| **grpc**     | `insecure_channel()` and `secure_channel()` (unary-unary) |
| **aiohttp**  | `ClientSession._request()` (async HTTP client)         |
| **botocore** | `URLLib3Session.send()` (all boto3 / AWS SDK calls)    |
| **pytest**   | pytest reporting hooks (test functions and methods)     |

## Python version support

| Package                 | Python  |
| ----------------------- | ------- |
| **traceloom** (client SDK) | >= 3.10 |
| **traceloom-server**       | >= 3.14 |
