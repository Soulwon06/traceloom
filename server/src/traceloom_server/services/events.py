"""Read-side queries and deletion operations for captured events."""

import re
import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from pydantic import TypeAdapter
from tortoise import connections

from traceloom_server.models import CapturedEvent, utcnow
from traceloom_server.services.epoch import bump_epoch, current_epoch
from traceloom_server.types import (
    EventData,
    EventDetail,
    EventHierarchy,
    EventIdsResponse,
    EventListResponse,
    EventStatsResponse,
    EventSummary,
    EventType,
    MetaResponse,
)

_event_data_adapter: TypeAdapter[EventData] = TypeAdapter(EventData)

# `rowid` is the insertion-order cursor exposed as `seq`. Selecting it costs
# nothing — SQLite stores it as the row key.
SUMMARY_COLUMNS = (
    "rowid as seq, id, timestamp, event_type, summary,"
    " COALESCE(json_extract(data, '$.app'), '') as app,"
    " COALESCE(json_extract(data, '$.session'), '') as session,"
    " json_extract(data, '$.host') as host,"
    " json_extract(data, '$.method') as method,"
    " json_extract(data, '$.status_code') as status_code,"
    " json_extract(data, '$.hierarchy') as hierarchy"
)


def hydrate_event_data(event_type: str, data: dict[str, Any]) -> EventData:
    """Validate a stored ``data`` blob against the typed ``EventData`` union.

    Injects ``event_type`` from the column into ``data`` if missing, so rows
    written before the typed-output refactor still round-trip without a
    migration.
    """
    data = {key: value for key, value in data.items() if key != "hierarchy"}
    if "event_type" not in data:
        data = {**data, "event_type": event_type}
    return _event_data_adapter.validate_python(data)


def _coerce_timestamp(value: datetime | str) -> datetime:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def _build_filters(
    *,
    event_type: str | None,
    host: str | None,
    method: str | None,
    status: int | None,
    search: str | None,
    app: str | None,
    session: str | None,
) -> tuple[str, list[str | int]]:
    """Build the shared WHERE clause and its bound parameters."""
    where_parts: list[str] = []
    params: list[str | int] = []

    if event_type:
        where_parts.append("event_type = ?")
        params.append(event_type)
    if host:
        where_parts.append("json_extract(data, '$.host') = ?")
        params.append(host)
    if method:
        where_parts.append("json_extract(data, '$.method') = ?")
        params.append(method.upper())
    if status:
        where_parts.append("json_extract(data, '$.status_code') = ?")
        params.append(status)
    if search:
        like_pattern = f"%{search}%"
        where_parts.append(
            "(summary LIKE ? COLLATE NOCASE OR data LIKE ? COLLATE NOCASE)"
        )
        params.extend([like_pattern, like_pattern])
    if app is not None:
        where_parts.append("COALESCE(json_extract(data, '$.app'), '') = ?")
        params.append(app)
    if session is not None:
        where_parts.append("COALESCE(json_extract(data, '$.session'), '') = ?")
        params.append(session)

    return " AND ".join(where_parts) if where_parts else "1=1", params


async def _max_seq(where_clause: str, params: list[str | int]) -> int:
    """Return the largest ``rowid`` matching the non-cursor filters."""
    db = connections.get("default")
    _, rows = await db.execute_query(
        "SELECT COALESCE(MAX(rowid), 0) as max_seq FROM captured_events"
        f" WHERE {where_clause}",
        list(params),
    )
    return int(rows[0]["max_seq"])


async def list_events(
    *,
    event_type: str | None = None,
    host: str | None = None,
    method: str | None = None,
    status: int | None = None,
    search: str | None = None,
    app: str | None = None,
    session: str | None = None,
    include_ancestors: bool = False,
    after_seq: int | None = None,
    before_seq: int | None = None,
    limit: int = 50,
) -> EventListResponse:
    """Return matching event summaries, newest first, with cursor state.

    ``after_seq`` returns the *oldest* ``limit`` events above the cursor, so a
    truncated delta leaves no gap: the caller advances to the page's largest
    ``seq`` and asks again. ``before_seq`` is its mirror for backfilling older
    events. Neither combines with ``include_ancestors``, whose ancestors are by
    definition older rows a cursor caller already holds.

    Raises:
        ValueError: If the cursor arguments contradict each other.
    """
    if after_seq is not None and before_seq is not None:
        raise ValueError("provide after_seq or before_seq, not both")
    if include_ancestors and (after_seq is not None or before_seq is not None):
        raise ValueError("include_ancestors cannot be combined with a seq cursor")

    where_clause, params = _build_filters(
        event_type=event_type,
        host=host,
        method=method,
        status=status,
        search=search,
        app=app,
        session=session,
    )
    db = connections.get("default")

    if after_seq is not None or before_seq is not None:
        # Page by rowid so the delta is contiguous, then present it newest-first
        # like every other listing.
        comparison, direction = (
            ("rowid > ?", "ASC") if after_seq is not None else ("rowid < ?", "DESC")
        )
        cursor = after_seq if after_seq is not None else before_seq
        _, rows = await db.execute_query(
            "WITH page(id) AS ("
            f" SELECT id FROM captured_events WHERE {comparison} AND {where_clause}"
            f" ORDER BY rowid {direction} LIMIT ?"
            ")"
            f" SELECT {SUMMARY_COLUMNS} FROM captured_events"
            " WHERE id IN (SELECT id FROM page)"
            " ORDER BY timestamp DESC, rowid DESC",
            [cursor, *params, limit],
        )
    elif include_ancestors:
        _, rows = await db.execute_query(
            "WITH RECURSIVE runtime_events("
            " id, trace_id, span_id, parent_span_id, role"
            ") AS MATERIALIZED ("
            " SELECT id,"
            " json_extract(data, '$.hierarchy.runtime.trace_id'),"
            " json_extract(data, '$.hierarchy.runtime.span_id'),"
            " json_extract(data, '$.hierarchy.runtime.parent_span_id'),"
            " json_extract(data, '$.hierarchy.runtime.role')"
            " FROM captured_events"
            " WHERE json_extract(data, '$.hierarchy.runtime.trace_id') IS NOT NULL"
            "), matched(id) AS ("
            f" SELECT id FROM captured_events WHERE {where_clause}"
            " ORDER BY timestamp DESC, rowid DESC LIMIT ?"
            "), included(id) AS ("
            " SELECT id FROM matched"
            " UNION"
            " SELECT parent.id"
            " FROM included"
            " JOIN runtime_events AS child ON child.id = included.id"
            " JOIN runtime_events AS parent"
            " ON parent.role = 'operation'"
            " AND parent.trace_id = child.trace_id"
            " AND parent.span_id"
            " = CASE"
            " WHEN child.role = 'annotation' THEN child.span_id"
            " ELSE child.parent_span_id"
            " END"
            ")"
            f" SELECT {SUMMARY_COLUMNS} FROM captured_events"
            " WHERE id IN (SELECT id FROM included)"
            " ORDER BY timestamp DESC, rowid DESC",
            [*params, limit],
        )
    else:
        _, rows = await db.execute_query(
            f"SELECT {SUMMARY_COLUMNS} FROM captured_events"
            f" WHERE {where_clause} ORDER BY timestamp DESC, rowid DESC LIMIT ?",
            [*params, limit],
        )

    return EventListResponse(
        epoch=current_epoch(),
        max_seq=await _max_seq(where_clause, params),
        events=[_row_to_summary(r) for r in rows],
    )


def _row_to_summary(row: dict[str, Any]) -> EventSummary:
    """Build a summary from one raw SQLite row of ``SUMMARY_COLUMNS``."""
    return EventSummary(
        id=str(row["id"]),
        seq=int(row["seq"]),
        timestamp=_coerce_timestamp(row["timestamp"]),
        event_type=cast(EventType, row["event_type"]),
        summary=row["summary"],
        app=row["app"],
        session=row["session"],
        host=row["host"],
        method=row["method"],
        status_code=row["status_code"],
        hierarchy=_hydrate_hierarchy(row["hierarchy"]),
    )


async def list_event_ids(
    *,
    event_type: str | None = None,
    host: str | None = None,
    method: str | None = None,
    status: int | None = None,
    search: str | None = None,
    app: str | None = None,
    session: str | None = None,
    limit: int = 10000,
) -> EventIdsResponse:
    """Return only the IDs of matching events, newest first.

    This is what makes body ``search`` work against a client-side store: the
    client holds every summary but no bodies, so the server matches and hands
    back an ID set to intersect.
    """
    where_clause, params = _build_filters(
        event_type=event_type,
        host=host,
        method=method,
        status=status,
        search=search,
        app=app,
        session=session,
    )
    db = connections.get("default")
    _, rows = await db.execute_query(
        f"SELECT id FROM captured_events WHERE {where_clause}"
        " ORDER BY timestamp DESC, rowid DESC LIMIT ?",
        [*params, limit],
    )
    return EventIdsResponse(epoch=current_epoch(), ids=[str(r["id"]) for r in rows])


def _status_class(status_code: int | None, event_type: str) -> str | None:
    """Bucket an HTTP status code, or flag an HTTP event that never got one."""
    if event_type not in {"http", "http_incoming"}:
        return None
    if status_code is None:
        return "error"
    return f"{status_code // 100}xx"


async def get_stats(
    *,
    event_type: str | None = None,
    host: str | None = None,
    method: str | None = None,
    status: int | None = None,
    search: str | None = None,
    app: str | None = None,
    session: str | None = None,
) -> EventStatsResponse:
    """Return aggregate counts for a filter without transferring the rows."""
    where_clause, params = _build_filters(
        event_type=event_type,
        host=host,
        method=method,
        status=status,
        search=search,
        app=app,
        session=session,
    )
    db = connections.get("default")
    _, rows = await db.execute_query(
        "SELECT event_type,"
        " json_extract(data, '$.status') as test_status,"
        " json_extract(data, '$.status_code') as status_code,"
        " COUNT(*) as count"
        f" FROM captured_events WHERE {where_clause}"
        " GROUP BY event_type, test_status, status_code",
        list(params),
    )

    total = 0
    by_event_type: dict[str, int] = {}
    by_test_status: dict[str, int] = {}
    by_status_class: dict[str, int] = {}
    for row in rows:
        count = int(row["count"])
        total += count
        row_type = str(row["event_type"])
        by_event_type[row_type] = by_event_type.get(row_type, 0) + count
        if row_type == "test" and row["test_status"] is not None:
            test_status = str(row["test_status"])
            by_test_status[test_status] = by_test_status.get(test_status, 0) + count
        status_class = _status_class(row["status_code"], row_type)
        if status_class is not None:
            by_status_class[status_class] = by_status_class.get(status_class, 0) + count

    return EventStatsResponse(
        epoch=current_epoch(),
        max_seq=await _max_seq(where_clause, params),
        total=total,
        by_event_type=dict(sorted(by_event_type.items())),
        by_test_status=dict(sorted(by_test_status.items())),
        by_status_class=dict(sorted(by_status_class.items())),
    )


async def get_event(event_id: str) -> EventDetail | None:
    """Return event detail by full UUID or eight-character ID prefix."""
    if re.fullmatch(r"[0-9a-fA-F]{8}", event_id):
        event = await CapturedEvent.filter(id__startswith=event_id.lower()).first()
    else:
        try:
            uuid.UUID(event_id)
        except ValueError:
            return None
        event = await CapturedEvent.get_or_none(id=event_id)
    if event is None:
        return None
    return EventDetail(
        id=str(event.id),
        seq=await _seq_of(str(event.id)),
        timestamp=event.timestamp,
        event_type=cast(EventType, event.event_type),
        summary=event.summary,
        app=event.data.get("app", ""),
        session=event.data.get("session", ""),
        host=event.data.get("host"),
        method=event.data.get("method"),
        status_code=event.data.get("status_code"),
        hierarchy=_hydrate_hierarchy(event.data.get("hierarchy")),
        data=hydrate_event_data(event.event_type, event.data),
    )


async def _seq_of(event_id: str) -> int:
    """Return one event's ``rowid``. Tortoise has no way to select it."""
    db = connections.get("default")
    _, rows = await db.execute_query(
        "SELECT rowid as seq FROM captured_events WHERE id = ?", [event_id]
    )
    return int(rows[0]["seq"]) if rows else 0


def _hydrate_hierarchy(value: Any) -> EventHierarchy | None:
    """Validate hierarchy loaded from either Tortoise or raw SQLite."""
    if value is None:
        return None
    if isinstance(value, str):
        return EventHierarchy.model_validate_json(value)
    return EventHierarchy.model_validate(value)


async def get_meta() -> MetaResponse:
    db = connections.get("default")

    _, host_rows = await db.execute_query(
        "SELECT DISTINCT json_extract(data, '$.host') as host"
        " FROM captured_events"
        " WHERE event_type IN ('http', 'http_incoming') AND host IS NOT NULL"
    )
    hosts = sorted({r["host"] for r in host_rows if r["host"]})

    _, method_rows = await db.execute_query(
        "SELECT DISTINCT json_extract(data, '$.method') as method"
        " FROM captured_events"
        " WHERE event_type IN ('http', 'http_incoming') AND method IS NOT NULL"
    )
    methods = sorted({r["method"] for r in method_rows if r["method"]})

    event_types: list[str] = (
        await CapturedEvent.all().distinct().values_list("event_type", flat=True)
    )  # type: ignore[assignment]

    _, app_rows = await db.execute_query(
        "SELECT DISTINCT COALESCE(json_extract(data, '$.app'), '') as app"
        " FROM captured_events"
    )
    apps = sorted({r["app"] for r in app_rows})

    _, session_rows = await db.execute_query(
        "SELECT DISTINCT COALESCE(json_extract(data, '$.session'), '') as session"
        " FROM captured_events"
    )
    sessions = sorted({r["session"] for r in session_rows})

    import traceloom_server  # noqa: PLC0415

    return MetaResponse(
        server_version=traceloom_server.__version__,
        hosts=hosts,
        methods=methods,
        event_types=sorted({cast(EventType, t) for t in event_types}),
        apps=apps,
        sessions=sessions,
    )


async def clear_events() -> None:
    await CapturedEvent.all().delete()
    bump_epoch()


async def delete_expired_events(
    *, retention_days: int, now: datetime | None = None
) -> int:
    """Delete expired events and return the number removed."""
    if retention_days < 0:
        raise ValueError("retention_days must be non-negative")
    if retention_days == 0:
        return 0

    cutoff = (now or utcnow()) - timedelta(days=retention_days)
    deleted_count = await CapturedEvent.filter(timestamp__lt=cutoff).delete()
    if deleted_count:
        bump_epoch()
    return deleted_count
