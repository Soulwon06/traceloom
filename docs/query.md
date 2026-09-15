# Query captured events

`traceloom query` reads captured events through the TraceLoom Server API. It works with a
local server or a remote one and never accesses the SQLite database directly.

## List events

Run the command without an event argument to load the newest events:

```bash
traceloom query
```

Text output shows the time, capture sequence, runtime hierarchy, summary, and an
eight-character event ID:

```text
16:07:51   1640  test          FAILED tests/test_checkout.py::test_provider_down  cac8220f
16:07:51   1641  ├─ http       POST /charge → ConnectionError  8b6e704a
16:07:51   1642  └─ log        WARNING payment provider unavailable  a9191556
```

The number after the time is the event's `seq` — its position in capture order. Pass the
highest one back with `--after-seq` to see only what has happened since.

When the results span more than one run, an `app/session` column appears after it so
every row says which run it belongs to. A dash marks an untagged value:

```text
16:07:51   1640  shop/checkout-debug  test          FAILED tests/test_checkout.py::test_pay  cac8220f
16:07:51   1641  shop/checkout-debug  └─ http       POST /charge → ConnectionError  8b6e704a
16:07:52   1642  shop/nightly-tests   test          PASSED tests/test_cart.py::test_total  3f2b91de
16:07:53   1643  -/-                  log           INFO uvicorn: startup complete  71ac0d54
```

The column is omitted when every event shares one app and session, which keeps the
common single-run listing uncluttered.

Use the displayed ID to open the complete event:

```bash
traceloom query 8b6e704a
```

### Filters

List filters map to the server's existing event query parameters:

| Option | Description |
| --- | --- |
| `--type TYPE` | Event type: `http`, `http_incoming`, `test`, `log`, or `exception` |
| `--host HOST` | Exact remote hostname for HTTP events |
| `--method METHOD` | Exact HTTP method |
| `--status STATUS` | Exact HTTP response status |
| `--search TEXT` | Text in the event summary or data |
| `--app NAME` | Exact application tag |
| `--session ID` | Exact session tag |
| `--ancestors` | Include runtime parents of matching records |
| `--after-seq SEQ` | Only events captured after this `seq`; cannot be combined with `--ancestors` |
| `--stats` | Print counts instead of events |
| `--limit N` | Number of matching records, from 1 to 10000; default: 50 |

Combine filters to isolate one part of a debugging run:

```bash
traceloom query \
  --session debug-payment \
  --type http \
  --status 500 \
  --ancestors
```

Filters apply to captured records before `--ancestors` adds runtime parents. The limit
counts matching records, so the response may contain more rows after ancestors are
added. A status filter matches calls that received a response; calls that failed before
receiving one have no status code.

## Tail a running command

Repeat the query with `--after-seq` set to the highest `seq` you have already seen, and
each call returns only what arrived since:

```bash
traceloom query --session debug-payment --after-seq 1642
```

## Count without listing

A test run can produce thousands of records, and usually the first question is just how
many of them failed. `--stats` answers that from the server without downloading any:

```bash
traceloom query --session debug-payment --stats
```

```text
total  1642

by type
  http   240
  log      2
  test  1400

by test status
  failed     3
  passed  1397

by status class
  2xx  237
  5xx    3
```

`--stats` accepts the same filters as a list query and also supports `--format json`.

## Output formats

Choose an output format with `--format`:

| Format | Behavior |
| --- | --- |
| `text` | Human-readable summaries with runtime hierarchy (default for lists) |
| `json` | One formatted JSON document; list results keep the `{epoch, max_seq, events}` envelope |
| `jsonl` | One list record per line for `jq` and shell pipelines |

```bash
traceloom query --session debug-payment --format json

traceloom query --session debug-payment --type http --format jsonl \
  | jq -r '[.id, .summary] | @tsv'
```

List queries return summary records and hierarchy metadata. They do not include the
event-specific `data` object with bodies, headers, tracebacks, or test failure details.
Fetch one event by ID when you need its full data.

Only query results go to stdout. Connection and response errors go to stderr, so JSON
and JSON Lines can be piped safely.

## Inspect one event

Pass a displayed eight-character ID, full UUID, or dashboard URL to retrieve a complete
event:

```bash
traceloom query 8b6e704a
traceloom query 8b6e704a-45a7-45a6-a6cd-533569fc8db7
traceloom query 'http://localhost:5110/#8b6e704a-45a7-45a6-a6cd-533569fc8db7'
```

Event lookups default to formatted JSON and include the full `data` object. An explicit
`--format text` prints its compact summary instead.

## Discover what was captured

`traceloom meta` lists every value the server can filter on, which is the fastest way to
learn which runs exist before narrowing a query:

```bash
traceloom meta
```

```text
server:       0.12.0
apps:         shop, worker
sessions:     checkout-debug, nightly-tests
event types:  exception, http, log, test
hosts:        api.stripe.com, api.openai.com
methods:      GET, POST
```

Unlike scanning a list, this covers the whole database rather than the newest records.
Pass `--format json` for scripting, and `--server` to point at another server.

```bash
traceloom meta --format json | jq -r '.sessions[]'
```

## Select a server

Both `traceloom query` and `traceloom meta` choose their server in this order:

1. `--server URL`
2. `TRACELOOM_URL`
3. The origin of a dashboard URL passed as the event argument
4. `http://localhost:5110`

The dashboard and API normally share one URL. During frontend development, a dashboard
URL on port 5111 maps to the API on port 5110.

```bash
traceloom query --server http://traceloom.internal:5110 --session debug-payment
TRACELOOM_URL=http://traceloom.internal:5110 traceloom query 8b6e704a
```

## Current limits

The server returns at most 10000 matching list records per call. Older records beyond
that are reachable only through the API's `before_seq` parameter, which `traceloom query`
does not expose yet. Text output reconstructs runtime hierarchy only among records in
one response, so use `--ancestors` when filters would otherwise omit runtime parents.
Event lookups return one record but do not yet expand its children, siblings, or
broader runtime context.
