# Evals for the traceloom skill

Three debugging tasks against a seeded TraceLoom server, chosen because each one punishes a
different failure mode the hierarchy changes introduced.

| Eval | What it tests | The trap |
| --- | --- | --- |
| `failed-outgoing-call` | A call that raised instead of returning a response | `status=500` filters cannot match it (`status_code` is null), and an identical URL appears in the other session as a decoy |
| `single-event-context` | Resolving one pasted event to what it happened inside | The warning looks alarming alone and benign once you see it belongs to a passing test |
| `pytest-failure-triage` | Attributing a failure correctly | The run's connection error sits next to the failing test but belongs to a different, passing one |

## Rebuilding the fixture

Start a server on a scratch database, then seed both sessions:

```bash
traceloom-server --port 5199 --db-path /tmp/seed.db --no-open &

traceloom run --server http://localhost:5199 --app shop --session nightly-tests \
    --capture-logs --log-level WARNING -- pytest examples/python/test_pytest_tracking.py -v

traceloom run --server http://localhost:5199 --app shop --session checkout-debug \
    --capture-logs --log-level INFO -- uvicorn examples.python.hierarchy_demo:app --port 8001 &
curl -X POST http://localhost:8001/checkout
curl -X POST http://localhost:8001/checkout
curl -X POST http://localhost:8001/checkout/provider-down
```

Event UUIDs in the assertions come from one particular seeding run. Reseeding produces new
UUIDs, so refresh them (or match on summaries instead) before grading against a fresh fixture.

Give each run its own copy of the database and its own port, so one run cannot disturb
another and no run can reach the developer's own TraceLoom server.

## Known limitation

On this 30-event fixture the evals do not discriminate between skill versions: a capable
model reconstructs the hierarchy from raw JSON whether or not the skill explains it, and both
versions passed everything. The measurable differences were in method and token cost, not
correctness. A fixture large enough that reading the flat list stops being practical would
test the guidance more honestly.
