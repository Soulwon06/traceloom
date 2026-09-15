# Tech Debt

## Testability: replace `patch("traceloom._config")` with a proper abstraction

**Problem.** Client SDK tests patch `traceloom._config` and transport functions directly via `unittest.mock.patch`. This applies across the board — FastAPI integration tests, httpx/grpc/aiohttp patch tests, and any future integration. Every test file needs to know the exact internal module path where the transport function is imported. This couples tests to internal module layout and makes refactoring fragile.

**Desired state.** A first-class way to inject a test-friendly transport without patching internals. For example:

- A swappable transport abstraction (`TraceLoomConfig(transport=...)`) so tests can pass a recording/mock transport at init time.
- Or a test helper like `traceloom.init_test()` that returns a collector object, wiring everything up without starting the background thread.

Either approach would let tests inspect captured payloads without knowing where `_config` or `send_http` live internally.

## Virtualize the event list

**Problem.** The dashboard now accumulates a whole session in memory, so a 10,000-event
run renders 10,476 list rows and about 150,000 DOM nodes, taking roughly 11.5 seconds to
paint (headless Chrome, 2026-08-05). The hierarchy projection is not the cost — it runs in
45 ms at that size. Rendering is.

**Desired state.** Windowed rendering over the flat `visibleEventIds` array that
`frontend/src/hierarchy/navigation.ts` already emits. `useListNavigation` will need a
`scrollToIndex` so keyboard navigation can reach rows that are not mounted.

## Shrink event summaries

**Problem.** List summaries run about 740 bytes per event even with no request or response
bodies attached, which makes the initial store load 7.4 MB for 10,000 events. Nearly all of
it is `hierarchy.group_memberships`, which repeats the same directory, file, class, and case
labels on every row of a run.

**Desired state.** Either omit memberships from summaries and let the client derive them,
or intern them — return a membership table once per response and reference it by ID from
each row. Cheaper to build than virtualization and cuts the initial load severalfold.

## Fold `max_seq` into the page query

**Problem.** `services/events.py:list_events` runs a second `SELECT MAX(rowid)` alongside
the page query to report `max_seq` over the whole matching set. Both scan the same
`json_extract` filter.

**Desired state.** One query, if the session scan ever shows up in a profile. It does not
today.

## Stop polling `/api/meta`

**Problem.** The filter dropdowns poll `/api/meta` every 10 seconds, and computing it
means five `SELECT DISTINCT json_extract(...)` scans of the whole table — 160 ms at
33,526 events, against 1.4 ms for an idle event delta. During a live run those scans
compete with capture writes on the same SQLite connection.

**Desired state.** Fetch `/api/meta` once on load and stop polling it. Event summaries
already carry `event_type`, `host`, `method`, `app`, and `session`, so the dropdown values
can be unioned out of the store deltas the dashboard is already receiving. Re-fetch only
when the epoch changes, since a clear or prune can only remove values and a union would
keep them forever.

## Make the epoch survive a server restart

**Problem.** The store epoch is `uuid4().hex[:8]` plus a counter, generated at import and
held in process memory, so every server restart invalidates every client store even when
the database file is untouched and `rowid` never moved. A plain restart does not renumber
anything; the rule exists only because a restart could have followed a `VACUUM` or a
swapped `TRACELOOM_DB_PATH`.

**Desired state.** Persist a random 32-bit value in `PRAGMA user_version` — it lives in
the SQLite file header, so no table, no column, and no migration, which matters given
`generate_schemas=True` and no migration tool. Re-randomize on clear-all, on a prune that
removed rows, and on any future `VACUUM`. Restarts then cost nothing, and a swapped
database file starts being detected, which the in-memory counter cannot do.
