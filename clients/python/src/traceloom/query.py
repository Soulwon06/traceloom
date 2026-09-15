"""Query captured events from a TraceLoom server."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Sequence
from typing import Any, cast

DEFAULT_SERVER_URL = "http://localhost:5110"
QUERY_TIMEOUT_SECONDS = 5
EVENT_LABEL_WIDTH = 13
SEQ_WIDTH = 5
META_FIELDS = (
    ("server", "server_version"),
    ("apps", "apps"),
    ("sessions", "sessions"),
    ("event types", "event_types"),
    ("hosts", "hosts"),
    ("methods", "methods"),
)


class QueryError(Exception):
    """A query error suitable for display at the command line."""


def query_events(
    *,
    target: str | None,
    server: str | None,
    event_type: str | None,
    host: str | None,
    method: str | None,
    status: int | None,
    search: str | None,
    app: str | None,
    session: str | None,
    ancestors: bool,
    after_seq: int | None = None,
    limit: int,
) -> dict[str, Any]:
    """Fetch one event detail or a list envelope.

    A list returns ``{epoch, max_seq, events}``. Pass ``after_seq`` — the
    ``max_seq`` of a previous call, or the ``seq`` of the newest event you
    already have — to fetch only what has arrived since.

    Raises:
        QueryError: If the target, server response, or connection is invalid.
    """
    event_id, server_url = _resolve_target(target, server)
    if event_id is not None:
        endpoint = f"{server_url.rstrip('/')}/api/events/{event_id}"
    else:
        params: dict[str, str | int] = {"limit": limit}
        optional_params = {
            "event_type": event_type,
            "host": host,
            "method": method,
            "status": status,
            "search": search,
            "app": app,
            "session": session,
            "after_seq": after_seq,
        }
        params.update(
            {key: value for key, value in optional_params.items() if value is not None}
        )
        if ancestors:
            params["include_ancestors"] = "true"
        endpoint = (
            f"{server_url.rstrip('/')}/api/events?{urllib.parse.urlencode(params)}"
        )

    payload = _get_json(endpoint, server_url)
    if not isinstance(payload, dict):
        raise QueryError("server returned an invalid event response")
    result = cast(dict[str, Any], payload)
    if event_id is None and not isinstance(result.get("events"), list):
        raise QueryError("server returned an invalid event list")
    return result


def query_stats(
    *,
    server: str | None,
    event_type: str | None,
    host: str | None,
    method: str | None,
    status: int | None,
    search: str | None,
    app: str | None,
    session: str | None,
) -> dict[str, Any]:
    """Fetch aggregate counts for a filter without downloading the events.

    Raises:
        QueryError: If the server response or connection is invalid.
    """
    _, server_url = _resolve_target(None, server)
    optional_params = {
        "event_type": event_type,
        "host": host,
        "method": method,
        "status": status,
        "search": search,
        "app": app,
        "session": session,
    }
    params = {key: value for key, value in optional_params.items() if value is not None}
    query = urllib.parse.urlencode(params)
    endpoint = f"{server_url.rstrip('/')}/api/events/stats" + (
        f"?{query}" if query else ""
    )

    payload = _get_json(endpoint, server_url)
    if not isinstance(payload, dict):
        raise QueryError("server returned an invalid stats response")
    stats = cast(dict[str, Any], payload)
    if "total" not in stats:
        raise QueryError("server returned an invalid stats response")
    return stats


def query_meta(*, server: str | None) -> dict[str, Any]:
    """Fetch the server's filter metadata.

    Raises:
        QueryError: If the server response or connection is invalid.
    """
    _, server_url = _resolve_target(None, server)
    payload = _get_json(f"{server_url.rstrip('/')}/api/meta", server_url)
    if not isinstance(payload, dict):
        raise QueryError("server returned an invalid metadata response")
    return cast(dict[str, Any], payload)


def _resolve_target(target: str | None, server: str | None) -> tuple[str | None, str]:
    """Resolve an optional event target and the server used to fetch it."""
    event_id: str | None = None
    inferred_server: str | None = None
    if target is not None:
        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme or parsed.netloc:
            event_id = _event_id_from_url(parsed)
            inferred_server = _server_from_dashboard_url(parsed)
        else:
            event_id = target
        if not re.fullmatch(r"[0-9a-fA-F]{8}", event_id):
            try:
                uuid.UUID(event_id)
            except ValueError as error:
                raise QueryError(f"invalid event ID: {event_id!r}") from error

    server_url = (
        server or os.environ.get("TRACELOOM_URL") or inferred_server or DEFAULT_SERVER_URL
    ).strip()
    if not server_url:
        raise QueryError("server URL cannot be empty")
    return event_id, server_url


def _event_id_from_url(parsed: urllib.parse.SplitResult) -> str:
    """Extract an event ID from a dashboard URL fragment."""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise QueryError("dashboard URL must use http or https")
    event_id = parsed.fragment.lstrip("/")
    if not event_id:
        raise QueryError("dashboard URL does not contain an event ID")
    return event_id


def _server_from_dashboard_url(parsed: urllib.parse.SplitResult) -> str:
    """Use the dashboard origin as the server, mapping dev port 5111 to 5110."""
    netloc = parsed.netloc
    if parsed.port == 5111:
        hostname = parsed.hostname or ""
        if ":" in hostname:
            hostname = f"[{hostname}]"
        netloc = f"{hostname}:5110"
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, netloc, path, "", ""))


def _get_json(endpoint: str, server_url: str) -> object:
    """Fetch and decode one JSON response."""
    try:
        with urllib.request.urlopen(
            endpoint, timeout=QUERY_TIMEOUT_SECONDS
        ) as response:  # noqa: S310
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise QueryError("event not found") from error
        raise QueryError(f"server returned {error.code}") from error
    except urllib.error.URLError as error:
        raise QueryError(f"failed to reach {server_url}: {error.reason}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QueryError("server returned invalid JSON") from error
    except ValueError as error:
        raise QueryError(f"invalid server URL {server_url!r}: {error}") from error


def print_events(
    payload: list[dict[str, Any]] | dict[str, Any], *, output_format: str
) -> None:
    """Print a query response in the requested format."""
    events = _extract_events(payload)
    if output_format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif output_format == "jsonl":
        for event in events:
            print(json.dumps(event, separators=(",", ":"), ensure_ascii=False))
    else:
        _print_text(events)


def print_meta(meta: dict[str, Any], *, output_format: str) -> None:
    """Print server filter metadata in the requested format."""
    if output_format == "json":
        print(json.dumps(meta, indent=2, ensure_ascii=False))
        return
    for label, key in META_FIELDS:
        value = meta.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            rendered = ", ".join(str(item) for item in value) if value else "-"
        else:
            rendered = str(value)
        print(f"{label + ':':<13} {rendered}")


def _extract_events(
    payload: list[dict[str, Any]] | dict[str, Any],
) -> list[dict[str, Any]]:
    """Unwrap a list envelope, a bare list, or one event detail."""
    if isinstance(payload, list):
        return payload
    events = payload.get("events")
    return cast(list[dict[str, Any]], events) if isinstance(events, list) else [payload]


def print_stats(payload: dict[str, Any], *, output_format: str) -> None:
    """Print aggregate counts in the requested format."""
    if output_format in {"json", "jsonl"}:
        indent = 2 if output_format == "json" else None
        print(json.dumps(payload, indent=indent, ensure_ascii=False))
        return

    print(f"total  {payload.get('total', 0)}")
    sections = (
        ("type", payload.get("by_event_type")),
        ("test status", payload.get("by_test_status")),
        ("status class", payload.get("by_status_class")),
    )
    for label, counts in sections:
        if not counts:
            continue
        print(f"\nby {label}")
        width = max(len(name) for name in counts)
        for name, count in counts.items():
            print(f"  {name:<{width}}  {count}")


def _print_text(events: Sequence[dict[str, Any]]) -> None:
    """Print compact summaries with runtime hierarchy indentation."""
    chronological = list(reversed(events))
    run_labels = _run_labels(events)
    operations: dict[tuple[str, str], dict[str, Any]] = {}
    for event in chronological:
        runtime = _runtime(event)
        if runtime.get("role") == "operation":
            operations[_runtime_key(runtime)] = event

    children: dict[str, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []
    for event in chronological:
        runtime = _runtime(event)
        parent_key: tuple[str, str] | None = None
        if runtime.get("role") == "annotation":
            parent_key = _runtime_key(runtime)
        elif runtime.get("parent_span_id"):
            parent_key = (
                str(runtime.get("trace_id", "")),
                str(runtime["parent_span_id"]),
            )
        parent = operations.get(parent_key) if parent_key is not None else None
        if parent is None or parent is event:
            roots.append(event)
        else:
            children.setdefault(str(parent.get("id", "")), []).append(event)

    run_width = max((len(label) for label in run_labels.values()), default=0)

    def print_node(event: dict[str, Any], branches: tuple[bool, ...] = ()) -> None:
        timestamp = str(event.get("timestamp", ""))
        time = timestamp[11:19] if len(timestamp) >= 19 else timestamp
        event_type = str(event.get("event_type", ""))
        event_id = str(event.get("id", ""))[:8]
        seq = f"{event.get('seq', ''):>{SEQ_WIDTH}}"
        event_label = f"{_tree_prefix(branches)}{event_type}"
        run = (
            f"{run_labels[str(event.get('id', ''))]:<{run_width}}  "
            if run_width
            else ""
        )
        print(
            f"{time}  {seq}  {run}{event_label:<{EVENT_LABEL_WIDTH}} "
            f"{_summary(event)}  {event_id}".rstrip()
        )
        if _runtime(event).get("role") == "operation":
            event_children = children.get(str(event.get("id", "")), [])
            for index, child in enumerate(event_children):
                print_node(child, (*branches, index == len(event_children) - 1))

    for root in roots:
        print_node(root)


def _run_labels(events: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Return per-event ``app/session`` labels, or nothing for a single run.

    Text output stays uncluttered when every event belongs to the same run.
    As soon as a response mixes runs, each row needs to say which one it came
    from, otherwise the rows are indistinguishable.
    """
    runs = {
        (str(event.get("app") or ""), str(event.get("session") or ""))
        for event in events
    }
    if len(runs) < 2:
        return {}
    return {
        str(event.get("id", "")): (
            f"{event.get('app') or '-'}/{event.get('session') or '-'}"
        )
        for event in events
    }


def _runtime(event: dict[str, Any]) -> dict[str, Any]:
    """Return an event's runtime hierarchy metadata."""
    hierarchy = event.get("hierarchy")
    if not isinstance(hierarchy, dict):
        return {}
    runtime = hierarchy.get("runtime")
    return runtime if isinstance(runtime, dict) else {}


def _tree_prefix(branches: tuple[bool, ...]) -> str:
    """Return box-drawing branches for one runtime tree node."""
    if not branches:
        return ""
    ancestors = "".join("   " if is_last else "│  " for is_last in branches[:-1])
    connector = "└─ " if branches[-1] else "├─ "
    return f"{ancestors}{connector}"


def _runtime_key(runtime: dict[str, Any]) -> tuple[str, str]:
    """Return the trace and span identity for runtime metadata."""
    return str(runtime.get("trace_id", "")), str(runtime.get("span_id", ""))


def _summary(event: dict[str, Any]) -> str:
    """Return a single-line event summary."""
    return str(event.get("summary", "")).replace("\n", " ")
