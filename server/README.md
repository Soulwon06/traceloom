<p align="center">
  <img src="../docs/assets/logo.png" alt="TraceLoom logo" width="160">
</p>

# TraceLoom Server

A local web dashboard for inspecting outgoing and incoming HTTP requests, pytest results, logs, and exceptions captured by the [traceloom](https://pypi.org/project/traceloom/) client SDK.

## Setup

```bash
uv sync --frozen
uv run traceloom-server
```

The server listens at `http://localhost:5110`.

Then install the client SDK and run your code with TraceLoom:

```bash
uv run traceloom run my_app.py
```

Outgoing HTTP requests, pytest results, unhandled exceptions, and optional log records are captured automatically.

Failed outgoing calls retain exception details. If a library raises after receiving a
response, TraceLoom stores both the response status and headers and the exception.

To capture tests, use the repository's frozen environment. The bundled plugin supports pytest 7 and later.

Pytest events include runtime trace and span IDs plus stable collection memberships.
Outgoing Requests, HTTPX, aiohttp, botocore, and gRPC calls inherit the active test
membership as child operations. The dashboard always shows runtime parenthood. Its
**Group** selector can add one available pytest level or remote-host grouping without
changing event deep links. Virtual groups merge only across adjacent siblings, which
preserves record order.
Timeline filters retain matching records' runtime ancestors, so filtered children remain
connected to their runtime context.

See the local `docs/guides/debug-pytest.md` for a runnable example and dashboard walkthrough.

Calls to the OpenAI, Anthropic, and Gemini APIs render as a readable conversation in the dashboard, with the system prompt, tool calls, and token usage broken out. The raw JSON stays one tab away.

## API

TraceLoom Server provides a JSON API for exploring captured events from the command line.
Install the `traceloom` client to query it without assembling API URLs:

```bash
traceloom query

traceloom query --type exception

traceloom query --method POST --host api.stripe.com --ancestors

traceloom query --app myapp --session debug-payment --format jsonl

traceloom query --session debug-payment --stats

traceloom query 5ae54ca2

# List every app, session, host, event type, and method captured
traceloom meta

# Clear all events
traceloom clear

# Equivalent HTTP API call
curl -X DELETE http://localhost:5110/api/events
```

Use `--server` or `TRACELOOM_URL` to select another server. A dashboard URL also
identifies its server; development URLs on port 5111 map to the API on port 5110.

## CLI Options

```bash
traceloom-server --host 0.0.0.0 --port 5110 --db-path /tmp/traceloom.db  # LAN access
```

## Event retention

TraceLoom Server deletes events older than seven days when it starts and every hour after that. Set `TRACELOOM_RETENTION_DAYS` to a non-negative integer to change the retention period:

```bash
TRACELOOM_RETENTION_DAYS=30 traceloom-server
```

Set it to `0` to keep events indefinitely. The server rejects negative or malformed values at startup.

## Requires

- Python >= 3.14

## Links

- [traceloom client SDK on PyPI](https://pypi.org/project/traceloom/)
