# API

TraceLoom Server provides a JSON API for exploring captured events from the command line.

The `traceloom` client wraps the list and detail endpoints for terminal use. See
[Query captured events](query.md) for the command's filters and output formats.

The full OpenAPI specification is available at [http://localhost:5110/openapi.json](http://localhost:5110/openapi.json), and an interactive playground at [http://localhost:5110/docs](http://localhost:5110/docs).

## List events

```bash
curl -s http://localhost:5110/api/events | python -m json.tool
```

### Query parameters

| Parameter    | Example          | Description                                   |
| ------------ | ---------------- | --------------------------------------------- |
| `event_type` | `test`           | Filter by event type: `http`, `http_incoming`, `test`, `log`, or `exception` |
| `method`     | `POST`           | Filter by HTTP method (HTTP events only)      |
| `host`       | `api.stripe.com` | Filter by hostname (HTTP events only)         |
| `status`     | `500`            | Filter by response status code (HTTP events only) |
| `search`     | `ValueError`     | Full-text search across summaries and event data |
| `app`        | `myapp`          | Filter by application name                     |
| `session`    | `debug-payment`  | Filter by session ID                           |
| `include_ancestors` | `true`     | Add the runtime ancestors of matching records  |
| `after_seq`  | `1640`           | Return only events captured after this `seq`, oldest first |
| `before_seq` | `500`            | Return only events captured before this `seq` (backfill) |
| `limit`      | `10`             | Max results (default: 200, max: 10000)        |

Note: `?app=` (empty value) returns only untagged events. Omitting `app` returns all events regardless of tag. The same applies to `session`.

Set `include_ancestors=true` to keep filtered records connected to their runtime tree.
For a matching annotation, the response includes its owning operation and that operation's
ancestors. The limit applies to matching records before ancestors are added, so the response
may contain more rows than `limit`. It cannot be combined with `after_seq` or `before_seq` —
those ancestors are older records a cursor caller already has, so the request returns 400.

Combine filters:

```bash
curl -s 'http://localhost:5110/api/events?app=myapp&session=debug-payment&event_type=http&include_ancestors=true&limit=5'
```

### Response format

The response is an envelope: the matching rows plus the cursor state needed to follow a run.

```json
{
  "epoch": "a1b2c3d4:0",
  "max_seq": 1642,
  "events": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "seq": 1642,
      "timestamp": "2026-04-12T21:00:02.560821Z",
      "event_type": "http",
      "summary": "GET /v1/charges → 200",
      "app": "myapp",
      "session": "debug-payment",
      "host": "api.stripe.com",
      "method": "GET",
      "status_code": 200,
      "hierarchy": null
    }
  ]
}
```

### Following a run

A test run produces thousands of events, and re-listing all of them on every check is
wasteful. Instead, remember `max_seq` and pass it back as `after_seq`:

```bash
curl -s 'http://localhost:5110/api/events?session=debug-payment&after_seq=1642&limit=10000'
```

Three fields make this work:

- **`seq`** is insertion order. Timestamps have one-second resolution and events are sent
  from a background thread, so timestamps cannot order a fast run — `seq` can.
- **`max_seq`** is the largest `seq` in the whole matching set, not just this page. If it
  is above the highest `seq` you received, the page was cut short by `limit`; advance your
  cursor to the highest `seq` you got and ask again.
- **`epoch`** changes whenever stored events are removed wholesale — a clear-all, a
  retention prune, or a server restart. When it differs from the one you last saw, your
  cursor is meaningless: discard what you have and fetch again without `after_seq`.

The optional `hierarchy` field contains runtime correlation and typed navigation group
memberships. Existing events captured without hierarchy return `null`. See
[Hierarchy and data model](data-model.md) for the field contract and projection rules.

Summary formats by event type:

- **http**: `METHOD /path → STATUS` (e.g., `POST /v1/charges → 201`)
- **http_incoming**: `METHOD /path → STATUS` (e.g., `GET /users/42 → 200`)
- **test**: `STATUS nodeid` (e.g., `FAILED tests/test_cart.py::test_total[empty]`)
- **log**: `LEVEL logger: message` (e.g., `WARNING myapp.auth: Token expired`)
- **exception**: `ExcType: message` (e.g., `ValueError: invalid literal...`)

## Count events

Returns aggregate counts for any filter, without transferring the events. Use it to
answer "did anything fail?" over a run of thousands of records.

```bash
curl -s 'http://localhost:5110/api/events/stats?session=debug-payment' | python -m json.tool
```

```json
{
  "epoch": "a1b2c3d4:0",
  "max_seq": 1642,
  "total": 1642,
  "by_event_type": { "http": 240, "log": 2, "test": 1400 },
  "by_test_status": { "failed": 3, "passed": 1397 },
  "by_status_class": { "2xx": 237, "5xx": 3 }
}
```

`by_status_class` buckets HTTP events by status class, plus `error` for calls that raised
before a response arrived. It accepts the same filters as the list endpoint.

## List matching IDs

Returns only the IDs of matching events. This is what makes search usable for a client
that already holds its own copy of the events but not their bodies.

```bash
curl -s 'http://localhost:5110/api/events/ids?search=ConnectTimeout'
```

```json
{ "epoch": "a1b2c3d4:0", "ids": ["550e8400-e29b-41d4-a716-446655440000"] }
```

## Get event details

Returns the full event data. The shape of `data` depends on the event type.
The endpoint accepts either the full UUID or the eight-character prefix shown by
`traceloom query`.

```bash
curl -s http://localhost:5110/api/events/{id} | python -m json.tool
```

### HTTP event data

```json
{
  "method": "GET",
  "url": "https://api.stripe.com/v1/charges",
  "host": "api.stripe.com",
  "status_code": 200,
  "duration_ms": 142,
  "library": "requests",
  "request_headers": { "Content-Type": "application/json" },
  "request_body": null,
  "response_headers": { "Content-Type": "application/json" },
  "response_body": "{\"id\": \"ch_123\"}"
}
```

### Log event data

```json
{
  "level": "WARNING",
  "logger_name": "myapp.auth",
  "message": "Token expired for user 42",
  "pathname": "/app/auth.py",
  "lineno": 87,
  "func_name": "validate_token",
  "extra": { "user_id": 42 }
}
```

### Exception event data

```json
{
  "exc_type": "ValueError",
  "exc_value": "invalid literal for int()",
  "exc_module": "builtins",
  "traceback_text": "Traceback (most recent call last):\n  ...",
  "frames": [
    {
      "filename": "app.py",
      "lineno": 42,
      "function": "main",
      "context_line": "    x = int(user_input)"
    }
  ]
}
```

### Test event data

```json
{
  "framework": "pytest",
  "framework_version": "9.0.2",
  "run_id": "019fa38d-42d3-7163-b366-28a5f8da1500",
  "worker_id": "master",
  "test_id": "tests/test_cart.py::test_total[empty]",
  "parameter_id": "empty",
  "name": "test_total[empty]",
  "path": "/workspace/project/tests/test_cart.py",
  "line": 18,
  "status": "failed",
  "duration_ms": 4.318,
  "setup_duration_ms": 1.102,
  "call_duration_ms": 2.947,
  "teardown_duration_ms": 0.269,
  "fixtures": ["cart"],
  "failures": [
    {
      "phase": "call",
      "exception_type": "AssertionError",
      "message": "assert 1 == 0",
      "traceback_text": "..."
    }
  ]
}
```

Test statuses are `passed`, `failed`, `error`, `skipped`, `xfailed`, or `xpassed`. The server's `test` event type is framework-neutral; the current client captures pytest.

## Get filter metadata

Returns distinct hosts, methods, event types, apps, and sessions for populating filter dropdowns. `traceloom meta` prints the same values as a readable table.

```bash
traceloom meta

# Equivalent HTTP API call
curl -s http://localhost:5110/api/meta | python -m json.tool
```

```json
{
  "hosts": ["api.openai.com", "api.stripe.com"],
  "methods": ["GET", "POST"],
  "event_types": ["exception", "http", "log", "test"],
  "apps": ["payment-service", "web-frontend"],
  "sessions": ["debug-payment-flow"]
}
```

## Clear all events

```bash
traceloom clear

# Equivalent HTTP API call
curl -X DELETE http://localhost:5110/api/events
```

## Capture endpoints

The TraceLoom client SDK posts captured events to typed endpoints, one per event type. You can also post directly from a script or tool, useful for capturing events from non-Python services.

### `POST /api/capture/http`

```json
{
  "id": "optional-uuid",
  "app": "myapp",
  "session": "debug-session",
  "duration_ms": 142,
  "request": {
    "method": "GET",
    "url": "https://api.stripe.com/v1/charges",
    "headers": { "Content-Type": "application/json" },
    "body": null,
    "body_size": 0
  },
  "response": {
    "status_code": 200,
    "headers": { "Content-Type": "application/json" },
    "body": "{\"id\": \"ch_123\"}",
    "body_size": 16
  },
  "meta": { "library": "requests" }
}
```

Every typed capture endpoint also accepts an optional top-level `hierarchy` object. See
[Hierarchy and data model](data-model.md) for runtime and group membership schemas.

If an outgoing call fails before producing a response, provide `error`:

```json
{
  "duration_ms": 5001,
  "request": {
    "method": "POST",
    "url": "https://api.stripe.com/v1/charges",
    "headers": {}
  },
  "error": {
    "type": "ConnectTimeout",
    "message": "connection timed out",
    "module": "httpx"
  }
}
```

HTTP capture payloads must contain `response`, `error`, or both. Send both when a
library raises because of a response, such as aiohttp with `raise_for_status=True` or a
gRPC status error. This preserves the response status and headers alongside the raised
exception.

### `POST /api/capture/log`

```json
{
  "id": "optional-uuid",
  "app": "myapp",
  "session": "debug-session",
  "data": {
    "level": "WARNING",
    "logger_name": "myapp.auth",
    "message": "Token expired for user 42",
    "pathname": "/app/auth.py",
    "lineno": 87,
    "func_name": "validate_token"
  }
}
```

### `POST /api/capture/exception`

```json
{
  "id": "optional-uuid",
  "app": "myapp",
  "session": "debug-session",
  "data": {
    "exc_type": "ValueError",
    "exc_value": "invalid literal for int()",
    "exc_module": "builtins",
    "traceback_text": "Traceback (most recent call last):\n  ...",
    "frames": [
      {
        "filename": "app.py",
        "lineno": 42,
        "function": "main",
        "context_line": "    x = int(user_input)"
      }
    ]
  }
}
```

### `POST /api/capture/test`

```json
{
  "id": "optional-uuid",
  "timestamp": "2026-07-27T12:34:56Z",
  "app": "myapp",
  "session": "debug-session",
  "data": {
    "framework": "pytest",
    "framework_version": "9.0.2",
    "run_id": "019fa38d-42d3-7163-b366-28a5f8da1500",
    "worker_id": "master",
    "test_id": "tests/test_cart.py::test_total[empty]",
    "parameter_id": "empty",
    "name": "test_total[empty]",
    "path": "/workspace/project/tests/test_cart.py",
    "line": 18,
    "status": "failed",
    "duration_ms": 4.318,
    "setup_duration_ms": 1.102,
    "call_duration_ms": 2.947,
    "teardown_duration_ms": 0.269,
    "fixtures": ["cart"],
    "failures": [
      {
        "phase": "call",
        "exception_type": "AssertionError",
        "message": "assert 1 == 0",
        "traceback_text": "..."
      }
    ]
  }
}
```

All typed capture endpoints return `201 Created` with `{"status": "ok"}`.

### `POST /api/capture` (deprecated)

The legacy HTTP-only endpoint. Accepts the same body shape as `/api/capture/http`. It is preserved for older client wheels (which only ever posted HTTP captures here) and will be removed in a future release. New integrations should use the typed endpoints above.
